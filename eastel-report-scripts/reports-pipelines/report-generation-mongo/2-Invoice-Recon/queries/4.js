/*
Query 4: Domestic MO voice on-net MOU.

Output:
{
  service_type: "Voice",
  charge_type: "MO",
  call_type: "On Net",
  mou: 113860
}
*/

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "VO",
      service_type_sub_cd: "MO",
      rating_group: "ONNET",
      roaming_destination_id: 87,
      opposite_number: { $regex: "^60" },
      $expr: {
        $gt: [
          { $strLenCP: { $ifNull: ["$opposite_number", ""] } },
          10
        ]
      }
    }
  },
  {
    $group: {
      _id: null,
      mou: {
        $sum: {
          $round: [
            {
              $divide: [
                { $toDouble: { $ifNull: ["$act_update_used_volume", 0] } },
                60
              ]
            },
            2
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Voice" },
      charge_type: { $literal: "MO" },
      call_type: { $literal: "On Net" },
      mou: 1
    }
  }
]);
